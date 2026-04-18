# Discovery Refactor Plan

`scripts/discover_jobs.py` currently combines the command-line interface, track
loading, HTTP transport, parsing helpers, discovery-mode dispatch, per-source
scrapers, matching rules, and some user- or track-specific assumptions in one
large file. That makes the project harder to open-source: contributors have to
edit the monolith to add source support, and user-specific discovery choices are
not clearly separated from reusable source integrations.

The target architecture keeps `scripts/discover_jobs.py` as the stable public
CLI entrypoint while moving reusable discovery code into an importable package
under `scripts/discover/`. New source support should be added as provider
modules under `scripts/discover/sources/`, registered by discovery mode, covered
by contract tests, and validated against live sources through the existing
source-quality workflow.

## Target Architecture

- `scripts/discover_jobs.py` remains the compatibility entrypoint for scheduled
  runs, repair workflows, existing tests, and direct CLI use.
- `scripts/discover/` owns reusable discovery internals: models, HTTP helpers,
  text/URL helpers, provider registry, and source-provider modules.
- `scripts/discover/sources/<provider>.py` modules implement one source family
  or one unavoidable bespoke source integration.
- Track-specific search terms and native source filters stay in
  `tracks/<track>/sources.json`.
- Future track/source matching rules should be structured config rather than
  executable per-track Python.
- `tests/contract/` defines a mechanical quality floor that every provider must
  satisfy.
- `scripts/eval_source_quality.py` remains the live canary and quality gate for
  real source integrations.

## Roadmap

### PR1: Provider Skeleton And First Exemplars

- Create the `scripts/discover/` package, registry, shared helpers, and provider
  contract tests.
- Migrate `iacr_jobs` and `lever_json` as exemplar providers.
- Keep all unmigrated handlers working through the legacy compatibility facade.
- Add contributor documentation and update the source-integration skill guidance.
- Preserve the current discovery artifact schema and CLI behavior.

### PR2: Reusable ATS Providers

- Migrate reusable board-family handlers such as Greenhouse, Workday, Ashby,
  Workable, Personio, Getro, and Eightfold.
- Add fixture coverage for each family.
- Introduce source-level `options` only when a migrated provider needs
  structured configuration that does not fit existing `filters`.

### PR3: Broad Boards And Structured Match Rules

- Migrate public and broad-board providers such as Hacker News, service.bund,
  YC Jobs, and IACR follow-ups.
- Move track-specific filtering logic, where practical, into structured
  track/source match rules.
- Avoid executable per-track filter plugins unless a maintained built-in hook is
  demonstrably necessary.

### PR4: Browser-Backed Providers

- Migrate Playwright/browser-backed providers while preserving optional browser
  behavior and current partial-coverage output when Playwright or browser
  binaries are unavailable.
- Add contract coverage for browser-unavailable behavior.

### PR5: Remaining Bespoke Providers

- Migrate the remaining bespoke company/public-service integrations.
- Update source-quality repair hints to point at provider modules instead of the
  monolithic `discover_jobs.py`.

### PR6: Stabilize Open-Source Contributor Surface

- Generate `docs/discovery_modes.md` from the registry.
- Ensure provider docs list supported URL shapes, filters, fixtures, and known
  limitations.
- Shrink `scripts/discover_jobs.py` to a true thin shim after all handlers and
  external callers are migrated.

## PR1 Non-Goals

- Do not migrate every handler.
- Do not change the discovery artifact JSON schema.
- Do not remove `scripts/discover_jobs.py` as a compatibility entrypoint.
- Do not introduce executable `tracks/<track>/filters.py` files.
- Do not redesign all track configuration at once.
- Do not require live network access for provider contract tests.
