from __future__ import annotations

import discover_jobs


def test_parse_source_specific_terms_reads_nested_search_terms_section():
    text = """
## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms
- cryptography

### Source-specific search terms
- Example Source — privacy, security
- Other Source [override] — mpc, garbled circuits
""".strip()

    mapping = discover_jobs.parse_source_specific_terms(text)

    assert mapping["Example Source"].mode == "append"
    assert mapping["Example Source"].terms == ["privacy", "security"]
    assert mapping["Other Source"].mode == "override"
    assert mapping["Other Source"].terms == ["mpc", "garbled circuits"]
