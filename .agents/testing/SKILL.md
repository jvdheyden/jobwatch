---
name: testing
description: Write and review behavior-focused tests for Jobwatch code, providers, agents, and workflows.
---

# Testing

## Principles

- Test **observable behavior and contracts**, not implementation details, private calls, or incidental strings. Exact text matters only when it is part of a real interface or output contract.
- Prefer **unit tests** for deterministic logic, shared **contract tests** for interchangeable components, and **integration tests** for interactions and state changes. Use a few end-to-end tests for critical workflows.
- Write the smallest test that catches a meaningful regression. Reuse existing coverage, avoid redundant tests, and mock dependencies rather than the behavior under test.
- Keep tests deterministic, isolated, and offline. Use realistic fixtures with expectations specified independently of production output.
- Add regression tests for bugs. Delete brittle or redundant tests without losing meaningful behavioral coverage.
- Do not force TDD for trivial refactors, config changes, or docs-only edits.

## Discovery quality

- Every registered provider should inherit shared contracts automatically. Add focused tests for capabilities or edge cases not covered by those contracts.
- Verify **which jobs are found**, not just output structure. Tests must fail when expected jobs are missed.
- Require evidence of correct extraction, genuinely empty results, deduplication, truthful failure/partial coverage, and reliable metadata. Include pagination, details, and browser behavior where applicable; do not silently skip required checks.
- Check real sources when introducing or repairing scrapers. Turn discovered failures into offline regressions; monitor live quality separately with periodically reviewed canaries.

## System quality

- Test persistent state across failures, partial scans, and reruns. Never treat a failed scan as successful or silently lose known jobs.
- Validate structured agent outputs. In workflow tests, fake external services and agents—not the orchestration being tested.
- Evaluate nondeterministic finding and ranking using reviewed examples, not exact generated prose.

## Contribution standard

New code must meet the same testing standard as existing code. Before finishing, ask: **What regression would these tests catch, and could a broken implementation still pass?** Run relevant tests and report unverified risks or skips.