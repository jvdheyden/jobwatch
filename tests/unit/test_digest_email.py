from __future__ import annotations

from datetime import date

import pytest

from digest_email import DigestEmailError, render_digest_email


def _ranked_payload(track: str = "core_crypto", count: int = 3) -> dict:
    return {
        "track": track,
        "generated_at": "2026-03-29T09:00:00Z",
        "jobs": [
            {
                "company": f"Company {index}",
                "title": f"Role {index}",
                "url": f"https://example.com/jobs/{index}",
                "fit_score": 10 - index / 10,
                "date_seen": f"2026-03-{index:02d}",
                "last_seen": f"2026-03-{index:02d}",
                "times_seen": index,
            }
            for index in range(1, count + 1)
        ],
    }


def test_render_digest_email_combines_new_jobs_and_ranked_overview(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    rendered = render_digest_email(digest, _ranked_payload(count=2))

    assert rendered.subject == "Core Crypto job digest: 1 new role, top score 9"
    assert rendered.body.startswith("Executive summary\nOne strong new role cleared the bar today.\n")
    assert "Date: 2026-03-29" not in rendered.body
    assert "New jobs\n1. Cryptographer - LayerZero Labs" in rendered.body
    assert "Fit: 9/10 | Recommendation: apply_now" in rendered.body
    assert "Ranked overview (top 2 of 2)" in rendered.body
    assert "Date seen: 2026-03-01" in rendered.body
    assert rendered.attachment_filename is None
    assert rendered.attachment_text is None
    assert "Seen:" not in rendered.body
    assert "Sources checked: 1 complete, 0 partial, 0 failed." in rendered.body
    assert "[[" not in rendered.body
    assert "Seen jobs to append" not in rendered.body
    assert "Source notes" not in rendered.body


def test_render_digest_email_combines_same_day_updates_and_sorts_roles(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_with_update.json")
    rendered = render_digest_email(digest, _ranked_payload(count=1))

    assert rendered.subject == "Core Crypto job digest: 2 new roles, top score 9"
    first = rendered.body.index("1. Cryptographer - LayerZero Labs")
    second = rendered.body.index("2. Privacy Engineer - Example Privacy Lab")
    assert first < second
    assert "One additional borderline role was surfaced later the same day." in rendered.body
    assert "Sources checked: 2 complete, 0 partial, 0 failed." in rendered.body


def test_render_digest_email_handles_no_new_roles_and_missing_ranked_overview(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    digest["runs"][0]["top_matches"] = []
    digest["runs"][0]["recommended_actions"] = []
    del digest["runs"][0]["executive_summary"]

    rendered = render_digest_email(digest, None)

    assert rendered.subject == "Core Crypto job digest: no new roles"
    assert "Executive summary\nNo summary provided." in rendered.body
    assert "New jobs\nNo new roles found today." in rendered.body
    assert "Ranked overview\nRanked overview unavailable." in rendered.body
    assert rendered.attachment_filename is None
    assert rendered.attachment_text is None


def test_render_digest_email_caps_ranked_overview_without_default_attachment(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    ranked = _ranked_payload(count=12)

    rendered = render_digest_email(digest, ranked, ranked_limit=3)

    assert "Ranked overview (top 3 of 12)" in rendered.body
    assert "Role 3 - Company 3" in rendered.body
    assert "Role 4 - Company 4" not in rendered.body
    assert rendered.attachment_filename is None
    assert rendered.attachment_text is None


def test_render_digest_email_shows_last_seen_only_when_different(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    ranked = _ranked_payload(count=1)
    ranked["jobs"][0]["last_seen"] = "2026-03-29"

    rendered = render_digest_email(digest, ranked)

    assert "Date seen: 2026-03-01 | Last seen: 2026-03-29" in rendered.body


def test_render_digest_email_shows_all_ranked_jobs_by_default(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    ranked = _ranked_payload(count=12)

    rendered = render_digest_email(digest, ranked)

    assert "Ranked overview (top 12 of 12)" in rendered.body
    assert "Role 12 - Company 12" in rendered.body
    assert rendered.html_body is not None
    assert "Ranked overview (top 12 of 12)" in rendered.html_body


def test_render_digest_email_html_bulletizes_multi_sentence_summary(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    digest["runs"][0]["executive_summary"] = "First point here. Second point follows. Third wraps it up."

    rendered = render_digest_email(digest, _ranked_payload(count=1))

    assert rendered.html_body is not None
    assert "<ul" in rendered.html_body
    assert rendered.html_body.count("<li") >= 3
    assert "First point here." in rendered.html_body


def test_render_digest_email_html_single_sentence_summary_stays_paragraph(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")

    rendered = render_digest_email(digest, _ranked_payload(count=1))

    assert rendered.html_body is not None
    assert "One strong new role cleared the bar today." in rendered.html_body
    # A single-sentence summary should not be rendered as a bullet list.
    summary_index = rendered.html_body.index("One strong new role cleared the bar today.")
    summary_context = rendered.html_body[summary_index - 40 : summary_index]
    assert "<li" not in summary_context


def test_render_digest_email_html_ranked_table_has_first_seen_only(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    ranked = _ranked_payload(count=1)
    ranked["jobs"][0]["date_seen"] = "2026-03-01"
    ranked["jobs"][0]["last_seen"] = "2026-03-29"

    rendered = render_digest_email(digest, ranked)

    assert rendered.html_body is not None
    assert ">First seen<" in rendered.html_body
    assert ">Last seen<" not in rendered.html_body
    assert "2026-03-01" in rendered.html_body
    # The last_seen date is no longer surfaced in the HTML ranked table.
    assert "2026-03-29" not in rendered.html_body


def test_render_digest_email_rejects_bad_ranked_limit(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")

    with pytest.raises(DigestEmailError, match="ranked_limit"):
        render_digest_email(digest, _ranked_payload(), ranked_limit=0)


def test_render_digest_email_filters_stale_ranked_jobs_when_as_of_given(load_json_fixture):
    digest = load_json_fixture("digests/core_crypto_minimal.json")
    ranked = {
        "track": "core_crypto",
        "generated_at": "2026-04-18T09:00:00Z",
        "jobs": [
            {
                "company": "Fresh Corp",
                "title": "Fresh Role",
                "url": "https://example.com/fresh",
                "fit_score": 9.0,
                "date_seen": "2026-04-10",
                "last_seen": "2026-04-10",
                "times_seen": 1,
            },
            {
                "company": "Stale Corp",
                "title": "Stale Role",
                "url": "https://example.com/stale",
                "fit_score": 8.0,
                "date_seen": "2026-03-01",
                "last_seen": "2026-03-01",
                "times_seen": 1,
            },
        ],
    }

    rendered = render_digest_email(digest, ranked, as_of=date(2026, 4, 18))

    assert "Fresh Role - Fresh Corp" in rendered.body
    assert "Stale Role - Stale Corp" not in rendered.body
    assert "Ranked overview (top 1 of 1)" in rendered.body
    assert rendered.attachment_filename is None
    assert rendered.attachment_text is None
