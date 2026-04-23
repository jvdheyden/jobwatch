<!-- GENERATED FILE: source of truth is .agents/skills/existing-source-curation/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: existing-source-curation
description: Add, evaluate, confirm, or enable a named employer or official source for an existing track. Resolve the official careers URL, choose a conservative discovery_mode, update sources.json, and escalate through integrate_next_source.py when needed.
---

# Skill: Curate a named source for an existing track

Use this skill when the user names a company or source and wants it added, evaluated, confirmed, or enabled for an existing track.

This skill is narrow in scope to one known employer or official source on an existing track. It may update track config and run the standard single-source integration workflow for that source when needed. Do not use it for broad source discovery, bulk removals, cadence sweeps, or unrelated source maintenance.

## Input

Read:
- `tracks/{track_slug}/prefs.md`
- `tracks/{track_slug}/sources.json`
- `tracks/{track_slug}/sources.md`
- `docs/source_curation.md`
- `docs/discovery_modes.md` when choosing or explaining supported `discovery_mode` values
- any user-supplied employer name, careers URL, board URL, or notes

If the track files are missing or the request is really for a new track, stop and hand control back to `set-up`.

## Workflow

### 1. Ground in the existing track

- Confirm the named source is at least plausibly relevant to the track preferences.
- Preserve existing sources unless the user explicitly asks to replace or remove one.
- Treat the request as narrow source curation, not open-ended employer discovery.

### 2. Resolve the official source

- Use `docs/source_curation.md` as the canonical reference for official-source selection and `discovery_mode` heuristics.
- If the user supplied a URL, verify whether it is the best official URL instead of accepting it blindly.
- Check the employer homepage and official careers path first. Prefer homepage-linked careers pages or ATS boards.
- Surface URL corrections when you replace a user-supplied URL with a better official one.

### 3. Normalize conservatively

- Prepare a normalized source entry suitable for `sources.json`.
- Infer a conservative `discovery_mode` from the URL or board family. Default to `html` when unclear.
- Keep clearly official sources even when they must use a supported fallback.
- If support looks uncertain or weak, do not bounce the user to `set-up`. Keep the source with the best current supported config, note the caveat, and decide whether to stop at curation or continue into single-source enablement based on the request shape.

### 4. Update the track and enable the source when needed

- If the source looks straightforward, treat the prompt as permission to update the track config directly.
- After changing `sources.json`, run:

```bash
JOB_AGENT_ROOT="$PWD" ./.venv/bin/python scripts/render_sources_md.py --track {track_slug}
```

- For `add <company> as a source to <track>` requests, treat end-to-end source enablement as intended functionality, not as a repo-development pivot.
- When the source needs more than a conservative fallback, use the standard single-source integration workflow:

```bash
./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --dry-run
./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD
```

- Let `scripts/integrate_next_source.py` own source-quality evaluation, config tuning, `source_state.json` updates, and any necessary provider logic via `scripts/source_integration.py`.
- For `evaluate` or `confirm` requests, report the caveat first and stop unless the user also wants the source landed or enabled now.
- Keep the user-facing result concise: source name, official URL, board family, chosen `discovery_mode`, cadence, any URL correction, whether single-source integration was run, and any remaining caveat.

## Boundaries

- Do not turn this skill into a broad source-pack recommender. For that, use `discover-sources` during `set-up`.
- Do not manually remove existing sources, change cadence, or retune unrelated search terms unless the user explicitly asks.
- Do not manually edit `source_state.json`; let `scripts/integrate_next_source.py` own those mutations during single-source enablement.
- Do not edit `match_rules.json` unless the request explicitly includes that work.
- Do not treat normal single-source enablement as a repo-development pivot. Only pivot to repo development when the user explicitly asks to change the shared integration workflow itself or to make manual shared-code edits outside the standard `scripts/integrate_next_source.py` path.
