"""Behavioral tests for the shared candidate-filter used by all discovery providers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from discover.helpers import should_keep_candidate  # noqa: E402


def test_product_manager_title_passes_with_matching_role_term():
    assert should_keep_candidate(
        title="Senior Product Manager, Music",
        matched_terms=["product manager"],
        searchable_text="Senior Product Manager, Music. Lead our music discovery product.",
    )


def test_role_term_match_outranks_unrelated_exclude_fragment():
    # Real posting (Musixmatch on Lever): "operations" is a function exclude,
    # but the title matches the track's explicit "product manager" term.
    assert should_keep_candidate(
        title="Product Manager, AI & Content Operations",
        matched_terms=["product manager"],
        searchable_text="Product Manager, AI & Content Operations. Own AI-assisted lyrics workflows.",
    )


def test_single_word_term_does_not_bypass_function_excludes():
    assert not should_keep_candidate(
        title="Product Marketing Manager",
        matched_terms=["product"],
        searchable_text="Product Marketing Manager. Position our product.",
    )


def test_sales_operations_manager_without_role_term_still_drops():
    assert not should_keep_candidate(
        title="Sales Operations Manager",
        matched_terms=["product"],
        searchable_text="Sales Operations Manager. Support the product org.",
    )


def test_manager_exclude_still_applies_without_role_term_match():
    # "manager" stays a function exclude for titles that do not match an
    # explicit multi-word track term.
    assert not should_keep_candidate(
        title="Engineering Manager, Cryptography",
        matched_terms=["cryptography"],
        searchable_text="Engineering Manager, Cryptography. We build privacy-preserving systems.",
    )


def test_account_executive_still_drops():
    assert not should_keep_candidate(
        title="Account Executive, EMEA",
        matched_terms=["product"],
        searchable_text="Account Executive, EMEA. Sell our product.",
    )


def test_cryptography_engineer_still_passes():
    assert should_keep_candidate(
        title="Senior Cryptography Engineer",
        matched_terms=["cryptography"],
        searchable_text="Senior Cryptography Engineer. Build cryptographic primitives.",
    )


def test_title_without_matched_terms_still_drops():
    assert not should_keep_candidate(
        title="Product Designer",
        matched_terms=[],
        searchable_text="Product Designer at Plain.",
    )
