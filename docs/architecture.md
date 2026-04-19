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

  subgraph Artifacts["On-disk artifacts"]
    DiscArt[(artifacts/discovery/&lt;track&gt;/&lt;date&gt;.json)]:::artifact
    StructDigest[(artifacts/digests/&lt;track&gt;/&lt;date&gt;.json)]:::artifact
    MdDigest[(tracks/&lt;track&gt;/digests/&lt;date&gt;.md)]:::artifact
    SrcState[(tracks/&lt;track&gt;/source_state.json)]:::artifact
    SeenJobs[(shared/seen_jobs.md)]:::artifact
    RankedOv[(shared/ranked_jobs/, ranked_overview.md)]:::artifact
    LogseqGraph[(LOGSEQ_GRAPH_DIR)]:::artifact
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
  DiscoverSources -.edits.-> SrcState
  Coding -.edits.-> RunTrack
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

## Where to read next

- [`AGENTS.md`](../AGENTS.md) — mode routing rules.
- [`README.md`](../README.md) — user-facing setup, manual runs, scheduling, delivery.
- [`docs/discovery_modes.md`](./discovery_modes.md) — auto-generated catalog of every supported provider.
- [`docs/contributing/adding-sources.md`](./contributing/adding-sources.md) — how to add a new discovery source.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — fork-and-PR workflow for code or doc contributions.
- Per-skill instructions live under `.agents/skills/<skill>/SKILL.md` (canonical) and mirror to `.claude/skills/<skill>/SKILL.md` via `bash scripts/sync_claude_skills.sh`.
