# Roadmap

_Last updated: 2026-05-14_

## Conventions

- Statuses: `new`, `in progress`, `complete`, `parked`
- `in progress` means there is active work, a concrete next step, and a linked plan for non-trivial work
- Non-trivial active items should link to a file in `docs/plans/`
- `parked` items must include a reason and revisit condition
- Keep entries short; move architecture, migration steps, interfaces, and test detail into linked plan docs
- Keep only recent completed items here; archive older ones elsewhere

## Instructions for AI Agents
- AI Agents should only append to fields, not delete any previous text. Exceptions are the fields Last updated and Status, which can be changed. Additionally, items may be moved between Status headers
- If you are instructed to complete multiple action items, or a sufficiently complex action item, do not implement them yourself. Rather, act as an orchestrator that writes the implementation plans and keeps track. Spawn subagents that implement the actual changes detailed in the plan.

Template:
RM-### — Title
- Status:
- Priority:
- Owner:
- Last updated:
- Links:
- Next step:
- Notes:


## New

## In progress
## Parked

## Completed
### RM-015 — Run source discovery for core\_crypto
- Status: complete
- Priority: M
- Owner: Jonas
- Last updated: 2026-05-14
- Links: [plan](plans/2026-05-14-roadmap-new-items.md)
- Next step: none
- Notes: Recommended a compact `core_crypto` source pack: Proton, OpenZeppelin, Aztec Labs, Succinct, Axiom, Brave, Decentriq, and Giesecke+Devrient, with Tools for Humanity / World deferred pending an Ashby board-slug URL-decoding fix.

### RM-014 — Analysis required: Why does the artifact often not include full listing description for Google / Anthropic etc
- Status: complete
- Priority: M
- Owner: Jonas
- Last updated: 2026-05-14
- Links: [plan](plans/2026-05-14-roadmap-new-items.md)
- Next step: none
- Notes: The main obstacle is provider output shape: Google and Greenhouse paths use role bodies for matching but do not preserve concise detail snippets in candidate notes; Google also lacks direct-page enrichment and can hit the browser page cap.

### RM-013 — Change codex\_hooks to hooks
- Status: complete
- Priority: M
- Owner: Jonas
- Last updated: 2026-05-14
- Links: [plan](plans/2026-05-14-roadmap-new-items.md)
- Next step: none
- Notes: Updated `/home/jvdh/.codex/config.toml` to use `[features].hooks = true`; verified `codex_hooks` no longer appears in that file.

### RM-012 — Telegram delivery for digests
- Status: complete
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-24
- Links: [plan](plans/2026-04-23-rm-012-telegram-delivery.md)
- Next step: none
- Notes: Manual runs, scheduled runs, setup guidance, and dry-run previews now support `--delivery telegram` via `scripts/send_digest_telegram.py`, with bot tokens loaded through the existing runtime-secret boundary.

### RM-010 — Add support for main email providers (gmail, fastmail, proton, hotmail)
- Status: complete
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: [plan](plans/2026-04-23-rm-010-email-provider-presets.md)
- Next step: none
- Notes: Provider presets now cover Gmail, Fastmail, Outlook.com/Hotmail, and Proton business SMTP on top of the post-`RM-009` runtime model. Proton Mail Bridge remains intentionally out of scope for this preset path.

### RM-009 — Move secrets out of project directory and import at runtime
- Status: complete
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: [plan](plans/2026-04-23-rm-009-runtime-secret-loading.md)
- Next step: none
- Notes: The shared runtime secret-loading boundary is in place, `.env.local` now keeps non-secrets plus `JOB_AGENT_SECRETS_FILE`, and plaintext repo-local `JOB_AGENT_SMTP_PASSWORD` is no longer supported.

### RM-011 — Simplify digest email output
- Status: complete
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: [plan](plans/2026-04-23-rm-011-email-output-cleanup.md)
- Next step: none
- Notes: The default digest email body now starts at `Executive summary`, the redundant body header/date lines are gone, and the ranked-overview attachment is no longer emitted by default.
