# Roadmap

_Last updated: 2026-04-23_

## Conventions

- Statuses: `new`, `in progress`, `complete`, `parked`
- `in progress` means there is active work, a concrete next step, and a linked plan for non-trivial work
- Non-trivial active items should link to a file in `docs/plans/`
- `parked` items must include a reason and revisit condition
- Keep entries short; move architecture, migration steps, interfaces, and test detail into linked plan docs
- Keep only recent completed items here; archive older ones elsewhere

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

### RM-009 — Move secrets out of project directory and import at runtime
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: none yet
- Next step: prioritize as the next active item after `RM-011`, then create an implementation plan
- Notes: Define a minimal runtime-loading boundary for secrets outside the repo. Keep scheduled non-interactive runs workable; defer keyring-style integration to a later phase.

### RM-010 — Add support for main email providers (gmail, fastmail, proton, hotmail)
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: none yet
- Next step: prioritize after `RM-009` settles the config and secrets boundary
- Notes: Add lightweight named-account and provider defaults on top of the post-`RM-009` runtime model. Keep provider logic shallow and preserve a custom SMTP escape hatch.

### RM-012 — Telegram delivery for digests
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: none yet
- Next step: prioritize after `RM-010` clarifies the delivery abstraction
- Notes: Add a lightweight digest delivery path without forcing heavy setup or duplicating the email/provider redesign.

## In progress

## Parked

## Completed
### RM-011 — Simplify digest email output
- Status: complete
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: [plan](plans/2026-04-23-rm-011-email-output-cleanup.md)
- Next step: none
- Notes: The default digest email body now starts at `Executive summary`, the redundant body header/date lines are gone, and the ranked-overview attachment is no longer emitted by default.
