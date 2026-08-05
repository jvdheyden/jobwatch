"""Shared defaults for discovery providers.

Provider-specific protocol constants should live in the provider module. This
module only holds defaults that are intentionally reused across providers.
"""

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_BROWSER_TIMEOUT_MS = 60_000
MAX_BROWSER_PAGES = 10

# JD-description enrichment bounds (agreed defaults from upstream issue #8).
JD_DESCRIPTION_CHAR_BUDGET = 4000
JD_FETCH_WALL_CLOCK_BUDGET_SECONDS = 60.0
JD_FETCH_HARD_CEILING = 200
