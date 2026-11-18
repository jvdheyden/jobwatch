# Source fixture ownership

Each mode's `contract.json` specifies expectations independently of its extractor.
The existing API/HTML/RSS fixtures are reduced, sanitized examples of supported
response structures. They are not evidence of today's live availability; original
capture dates are not available for every inherited fixture. The browser DOM packs
added in the testing overhaul are synthetic observations matching each strategy's
selectors and embedded payload shape, with independently named vacancies and
navigation/noise records. They do not certify live selectors are still correct.

For a new live regression, add a nearby provenance note with the source URL,
capture date, reason for capture and redactions. Preserve the structure needed to
reproduce the failure (including pagination totals and alternate locations), remove
personal data/tokens, and specify expected job identities and relevant metadata by
reading the source. Never refresh expected output automatically from the scraper.

See [provider contracts](../../../docs/testing.md#provider-contracts) for the pack
layout and [live assurance](../../../docs/testing.md#live-source-assurance) for
canaries and representative installation checks.
