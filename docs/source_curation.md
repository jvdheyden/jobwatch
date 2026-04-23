# Official Source And `discovery_mode` Heuristics

Use this guide when a skill needs to identify the best official source URL for a track or choose a conservative `discovery_mode`.

## Official source priority

- Start from the employer homepage when possible. Check the header, footer, and primary navigation for links such as `Careers`, `Jobs`, `Join us`, or `Work with us` before doing broader search.
- Prefer official careers pages and homepage-linked ATS destinations over third-party aggregators.
- Treat homepage-linked ATS boards as official when they are clearly tied to the employer, including hosted boards on Greenhouse, Lever, Ashby, Workday, Workable, Getro, Personio, Recruitee, and similar providers.
- If the user supplied a direct ATS or careers URL, verify it against the employer homepage before accepting or replacing it.
- Only keep third-party boards when the workflow explicitly calls for broad-board discovery or the user asked for them.

## `discovery_mode` selection

- Use a mode listed in `docs/discovery_modes.md`. Do not invent a new `discovery_mode`.
- Common mappings:
  - Workday career pages or APIs: `workday_api`
  - Greenhouse boards: `greenhouse_api`
  - Lever boards: `lever_json`
  - Ashby boards with usable API responses: `ashby_api`
  - Ashby boards without reliable API clues: `ashby_html`
  - Workable boards: `workable_api`
  - Getro collection boards: `getro_api`
  - Personio pages: `personio_page`
  - Recruitee inline pages: `recruitee_inline`
  - YC jobs role boards: `yc_jobs_board`
  - Hacker News jobs pages: `hackernews_jobs`
  - service.bund search URLs: `service_bund_search`
  - IACR jobs: `iacr_jobs`
  - Other official ATS pages without dedicated support: `html`
  - Unknown or custom official pages: `html`
- If more than one mode seems plausible, choose the most conservative supported option and note the uncertainty.
- If a source is clearly official but the dedicated support is weak or unknown, keep it with the best supported fallback, usually `html`, rather than inventing a mode or dropping the source outright.

## Fallback and escalation

- If an employer homepage links directly to an official ATS board, keep that board as the source of truth even when it must fall back to `html`.
- When support looks uncertain or weak, surface the caveat and suggest source-integration follow-up instead of auto-escalating into provider-development work.
- Keep source selection and source integration separate: picking the official URL and the best current `discovery_mode` comes first; adding provider support belongs under `scripts/discover/sources/` with fixtures and contract tests.
