# Architecture Overview

This repo runs an agent-assisted job-search workflow. Each track combines deterministic Python helpers under `scripts/` with agent-driven skills under `.agents/skills/`. This page is the high-level map; per-source detail lives in the auto-generated [`discovery_modes.md`](./discovery_modes.md).

## Work modes

[`AGENTS.md`](../AGENTS.md) routes every prompt to one of four modes:

| Mode | Trigger | Lives in |
| --- | --- | --- |
| Track run | Scheduled or user prompt to run a track and produce a digest | `tracks/<track>/AGENTS.md`, agent skills, `scripts/` |
| Track setup | Prompt to create/scaffold a new search track | `set-up` skill |
| Existing-track source curation | Prompt to add/evaluate a single named employer or source for an existing track | `tracks/<track>/sources.json` + `scripts/render_sources_md.py` |
| Repo development | Prompt to change code, tests, skills, or docs | `coding` skill, `scripts/`, `tests/` |

## Component map

The flowchart shows how the agent skills, deterministic scripts, and on-disk artifacts interact across all four modes. Solid arrows are direct calls or invocations; dashed arrows are read/write of artifacts.

```mermaid
flowchart LR
  classDef agent fill:#e6f0ff,stroke:#3366cc,color:#000
  classDef script fill:#fff5e6,stroke:#cc8833,color:#000
  classDef artifact fill:#eef7ee,stroke:#339955,color:#000

  subgraph Skills["Agent skills (.agents/skills/)"]
    SetUp[set-up]:::agent
    FindJobs[find-jobs]:::agent
    RankJobs[rank-jobs]:::agent
    DiscoverSources[discover-sources]:::agent
    Coding[coding]:::agent
  end

  subgraph Scheduler["Scheduler entry"]
    Cron[(cron / launchd)]
    Sched[scripts/run_scheduled_jobs.sh]:::script
  end

  subgraph TrackRun["Track-run pipeline (scripts/)"]
    RunTrack[run_track.sh]:::script
    Discover[discover_jobs.py]:::script
    Agent[(agent: claude or codex<br/>uses find-jobs / rank-jobs / discover-sources)]:::agent
    UpdState[update_source_state.py]:::script
    Render[render_digest.py]:::script
    Seen[update_seen_jobs.py]:::script
    Ranked[update_ranked_overview.py]:::script
  end

  subgraph Delivery["Optional delivery"]
    Logseq[sync_to_logseq.sh]:::script
    Email[send_digest_email.py]:::script
  end

  subgraph SourceHealth["Source repair loop (manual)"]
    Repair[repair_source.py]:::script
    Eval[eval_source_quality.py<br/>+ source_quality.review_source_with_llm]:::script
    Coder[(coder agent: claude or codex<br/>uses coding skill)]:::agent
  end

  subgraph Artifacts["On-disk artifacts"]
    DiscArt[(artifacts/discovery/&lt;track&gt;/&lt;date&gt;.json)]:::artifact
    StructDigest[(artifacts/digests/&lt;track&gt;/&lt;date&gt;.json)]:::artifact
    MdDigest[(tracks/&lt;track&gt;/digests/&lt;date&gt;.md)]:::artifact
    SrcState[(tracks/&lt;track&gt;/source_state.json)]:::artifact
    SeenJobs[(shared/seen_jobs.md)]:::artifact
    RankedOv[(shared/ranked_jobs/, ranked_overview.md)]:::artifact
    LogseqGraph[(LOGSEQ_GRAPH_DIR)]:::artifact
    EvalArt[(artifacts/evals/&lt;track&gt;/&lt;source&gt;/&lt;date&gt;.json<br/>eval + embedded repair_ticket)]:::artifact
  end

  Cron --> Sched
  Sched -->|reads .schedule.local| RunTrack
  RunTrack --> Discover
  Discover -.writes.-> DiscArt
  RunTrack --> Agent
  Agent -.reads.-> DiscArt
  Agent -.writes.-> StructDigest
  RunTrack --> UpdState
  UpdState -.writes.-> SrcState
  RunTrack --> Render
  Render -.reads.-> StructDigest
  Render -.writes.-> MdDigest
  RunTrack --> Seen
  Seen -.writes.-> SeenJobs
  RunTrack --> Ranked
  Ranked -.writes.-> RankedOv
  RunTrack --> Logseq
  Logseq -.reads.-> MdDigest
  Logseq -.writes.-> LogseqGraph
  RunTrack --> Email
  Email -.reads.-> StructDigest

  SetUp -.scaffolds.-> SrcState
  SetUp -.runs eval + repair on top probed sources.-> Repair
  DiscoverSources -.edits.-> SrcState
  Coding -.edits.-> RunTrack

  Repair --> Eval
  Eval -.reads.-> DiscArt
  Eval -.writes.-> EvalArt
  Repair -.reads ticket from.-> EvalArt
  Repair --> Coder
  Coder -.edits.-> Discover
  Repair --> Discover
```

## Scheduled track run, end to end

The sequence diagram shows what happens for a single scheduled run.

```mermaid
sequenceDiagram
  autonumber
  participant Cron as cron / launchd
  participant Sched as run_scheduled_jobs.sh
  participant Track as run_track.sh
  participant Disc as discover_jobs.py
  participant Agent as Agent (claude/codex)
  participant Post as Post-processing scripts
  participant Deliv as Delivery (logseq/email)

  Cron->>Sched: tick (per-minute dispatcher)
  Sched->>Sched: read .schedule.local, find due tracks
  Sched->>Track: run_track.sh --track <slug> [--delivery ...]
  Track->>Disc: discover_jobs.py --track <slug> --today <date>
  Disc-->>Track: artifacts/discovery/<track>/<date>.json
  Track->>Agent: invoke with prompt + tracks/<track>/AGENTS.md
  Agent->>Agent: find-jobs (filter, dedupe), rank-jobs (score)
  Agent-->>Track: artifacts/digests/<track>/<date>.json
  Track->>Post: update_source_state.py
  Track->>Post: render_digest.py (markdown)
  Track->>Post: update_seen_jobs.py
  Track->>Post: update_ranked_overview.py
  alt --delivery logseq
    Track->>Deliv: sync_to_logseq.sh
  end
  alt --delivery email
    Track->>Deliv: send_digest_email.py
  end
  Track-->>Sched: exit status
```

## Source repair loop

Sources break: a job board changes its HTML, an ATS shifts an API field, a canary stops resolving. The repair loop in `scripts/repair_source.py` automates the inner cycle of detecting that a source is broken, dispatching a coding agent to fix it, and re-checking the result.

The loop is invoked two ways. During track setup, the `set-up` skill runs `eval_source_quality.py` on newly probed sources with canaries and auto-dispatches `repair_source.py` for the top 2 `repair_needed` sources by default (budget-capped — see `.agents/skills/set-up/SKILL.md` section 4c). Outside setup, run it manually per source for sources beyond that budget, sources added to an existing track later, or lower-importance sources you want to upgrade. It is not triggered from scheduled track runs.

The reviewer role lives **inside each re-eval cycle**, not as a separate step between fix attempts. `scripts/eval_source_quality.py` runs a deterministic validator (`source_quality.validate_source_coverage`) and an LLM reviewer (`source_quality.review_source_with_llm`) over the discovery output; if defects remain, the eval emits a `repair_ticket` and the next coder attempt fires.

```mermaid
sequenceDiagram
  autonumber
  participant Dev as Developer
  participant Repair as repair_source.py
  participant Eval as eval_source_quality.py<br/>(deterministic + LLM reviewer)
  participant Disc as discover_jobs.py
  participant Coder as Coder agent (claude/codex)<br/>uses coding skill

  Dev->>Repair: repair_source.py --track <slug> --source "<Name>" --today <date> --canary-title "..."
  loop until pass / blocked / retry_limit
    Repair->>Eval: evaluate latest discovery artifact
    Eval-->>Repair: eval JSON + final_status (+ repair_ticket if repair_needed)
    alt final_status == pass
      Repair-->>Dev: exit pass
    else final_status == blocked
      Repair-->>Dev: exit blocked
    else repair_needed and attempts < max
      Repair->>Coder: prompt built from repair_ticket<br/>(failure_mode, target_outcome, suggested_strategy, likely_file)
      Coder-->>Repair: edits in working tree
      Repair->>Disc: rediscover the source
      Disc-->>Repair: fresh discovery artifact
    else attempts >= max
      Repair-->>Dev: exit retry_limit
    end
  end
```

### Repair artifacts

All repair-loop output lands under `artifacts/evals/<track>/<source_slug>/`:

- `<date>.json` — eval result with embedded `repair_ticket` (the canonical input to the next coder attempt)
- `<date>.repair_loop.json` — summary of the entire loop (phases, attempts, final status)
- `<date>.discovery.json` — fresh discovery artifact captured after a coder attempt
- `<date>.attempt<N>.coder.stdout.jsonl` / `.stderr.log` / `.last_message.txt` — per-attempt coder logs
- `<date>.attempt<N>.postmortem.json` — failure analysis written after a blocked attempt; fed back into the next attempt's prompt as prior context

When a repair lands a working fix, push the branch from your fork and open a PR per [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the loop ends at the working-tree fix; upstreaming is the standard fork-and-PR flow.

## Where to read next

- [`AGENTS.md`](../AGENTS.md) — mode routing rules.
- [`README.md`](../README.md) — user-facing setup, manual runs, scheduling, delivery.
- [`docs/discovery_modes.md`](./discovery_modes.md) — auto-generated catalog of every supported provider.
- [`docs/contributing/adding-sources.md`](./contributing/adding-sources.md) — how to add a new discovery source.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — fork-and-PR workflow for code or doc contributions.
- Per-skill instructions live under `.agents/skills/<skill>/SKILL.md` (canonical) and mirror to `.claude/skills/<skill>/SKILL.md` via `bash scripts/sync_claude_skills.sh`.
