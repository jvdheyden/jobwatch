# Bugs found during agrar_wuppertal track setup

Discovered 2026-04-14. Three config/parser issues that silently degrade discovery for the `agrar_wuppertal` track, plus one wrapper-script bug that prevents scheduled runs entirely.

## Bug 1 — Scheduled Claude runs start in the wrong working directory

**Status**: plan written, not yet fixed.

**Symptom**: The 08:00 cron run on 2026-04-14 produced a discovery artifact but no digest. The log shows `"cwd":"/home/jvdh"` — Claude was launched with the user's home directory, not the repo root.

**Root cause**: `scripts/run_track.sh` `run_agent_command` — the `codex` branch passes `-C "$ROOT"` to set the working directory, but the `claude` branch does not. Under cron, CWD is `$HOME`. Claude then found a stale second checkout at `/home/jvdh/Documents/jobsearch/` (no `agrar_wuppertal` track there) and gave up.

**Fix**: Wrap the `claude` branch in `(cd "$ROOT" && ...)` to mirror the codex branch.

**File**: `scripts/run_track.sh`, lines 445–453.

## Bug 2 — Source-specific search terms use wrong separator format

**Status**: open.

**Symptom**: `discover_jobs.py --list-sources` shows identical track-wide terms on every source. Source-specific terms for Bayer and agrajo are silently ignored.

**Root cause**: The parser at `scripts/discover_jobs.py:695` (`parse_source_specific_terms`) expects em-dash (`—`) as the separator between source name and term list:

```
- Source Name — term1, term2, term3
```

Our `tracks/agrar_wuppertal/sources.md` uses a colon:

```
- Bayer Careers — Monheim: crop science, pflanzenschutz, agronom, ...
```

The colon form does not match `split_source_directive`, so these lines contribute nothing.

**Evidence**: `tests/unit/test_discover_jobs_config.py:19` confirms the expected format.

**Fix**: Rewrite the source-specific search-term lines in `sources.md` with em-dash separators instead of colons. Also requires fixing bug 3 first (source names with em-dashes).

**File**: `tracks/agrar_wuppertal/sources.md`, section "Source-specific search terms".

## Bug 3 — Source names containing em-dashes collide with the parser's separator

**Status**: open.

**Symptom**: Even with the correct em-dash separator format, source-specific terms and filters are never applied because the parser extracts the wrong source name.

**Root cause**: `split_source_directive` (`scripts/discover_jobs.py:681`) splits each bullet on the **first** em-dash:

```python
if "\u2014" in content:
    source, value = content.split("\u2014", 1)
```

All source names in `agrar_wuppertal/sources.md` contain em-dashes:

- `Bayer Careers — Monheim`
- `Landwirtschaftskammer NRW — Stellen`
- `agrajo — NRW`
- `karriere.nrw — LWK Dienststelle`
- etc.

For a correctly formatted filter line like:

```
- Bayer Careers — Monheim — location: Monheim am Rhein, Germany
```

The parser splits at the first em-dash: `source_name="Bayer Careers"`, `value="Monheim — location: ..."`. The lookup at `discover_jobs.py:770` against the real source name `"Bayer Careers — Monheim"` fails silently.

The test fixtures (`tests/unit/test_discover_jobs_config.py`) all use plain source names without em-dashes (`Google`, `Example Source`, `Monthly`). The set-up skill template does not warn against em-dashes in source names.

**Fix options**:

- **Option A (config-only)**: Rename sources to avoid em-dashes (e.g. `Bayer Careers Monheim`, `agrajo NRW`). Simple, no parser change, but imposes a naming constraint on all future tracks.
- **Option B (parser change)**: Change `split_source_directive` to handle ambiguity, e.g. match source names against the known source list from the table, or use a different delimiter for the directive separator. Higher risk, touches shared code.

**Files**: `tracks/agrar_wuppertal/sources.md` (source name column), and optionally `scripts/discover_jobs.py:681` and the set-up skill template.

## Bug 4 — Bayer `discovery_mode: workday_api` is wrong

**Status**: open.

**Symptom**: Bayer source likely errors silently during discovery. The 2026-04-14 discovery artifact contained only 1 of 7 configured sources (Landwirtschaftskammer NRW).

**Root cause**: `discover_workday_api` (`scripts/discover_jobs.py:3711`) hard-rejects URLs that are not `myworkdayjobs.com`:

```python
if "myworkdayjobs.com" not in parsed_source.netloc:
    raise ValueError(...)
```

Bayer's career board lives at `jobs.bayer.com`, which is SAP SuccessFactors, not Workday. The `workday_api` mode throws on this URL.

**Additional context**: Even on a real Workday board, `discover_workday_api` does not consult `source.filters` — it only iterates search terms. The `location` filter we configured for Bayer would not be applied by the workday scraper. Only the Google Jobs discovery path (`discover_jobs.py:4465`) currently honours `source.filters`.

**Fix**: Change Bayer's `discovery_mode` to `html` in `sources.md`. For location narrowing, either encode the Monheim filter into the source URL as a search parameter, or rely on post-fetch keyword filtering in the search terms.

**File**: `tracks/agrar_wuppertal/sources.md`, Bayer row in "Check every 3 runs" table.

## Recommended fix order

1. Bug 1 (CWD fix in `run_track.sh`) — unblocks scheduled runs entirely.
2. Bug 3 (rename sources to remove em-dashes) — unblocks bugs 2 and 4.
3. Bug 2 (rewrite source-specific terms with em-dash separator) — now works after rename.
4. Bug 4 (change Bayer to `discovery_mode: html`, drop non-functional location filter or encode it into URL).
5. Optional: update set-up skill template to warn against em-dashes in source names.
